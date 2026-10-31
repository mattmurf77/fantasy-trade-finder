"""Server error alerts through Sentry (GNG-1) and the feedback_received alert
(SUP-M7): backend/error_alerts.py and its server.py wiring.

docs/plans/server-error-alerts/scope.md §3. Nothing leaves the process: a
case that turns Sentry on uses a fake DSN and a recording transport (the
`sentry` fixture), whose teardown closes the client and resets the SDK's
global client, so no other test runs with Sentry active (the autouse guard
asserts it before and after every test here). Counts are of events captured
on the test's own thread, so a stray daemon thread left by another test
can't change them; the leak checks read every envelope.

  (a) no SENTRY_DSN: init is False, no client, notify and the 5xx hook send
      nothing, and the SDK is never imported; a malformed DSN doesn't fail boot
  (b) a raising route: exactly one event, with the stack
  (c) a handled 503: one http_5xx (route/status/method tags, fingerprint);
      a 404: none; a handled 500 after log.exception: one
  (d) one _cleanup_loop pass with a step raising: one event, the guard's message
  (e) a daily_tick step raising: one event
  (f) the scrub end to end (no secret in the envelope bytes), scrub_event's
      patterns, and fail closed
  (g) POST /api/feedback: one feedback_received carrying exactly feedback_id
      and kind, nothing of the note; a duplicate: none
  (h) a thread started in a request: its event carries no request

Sabotage record (2026-10-31; each applied, observed red, restored green):
  no-DSN guard removed in init_error_alerts       -> (a) RED (at setup: importing
                                                     backend.server turned Sentry on)
  report_5xx's last-event-id check removed        -> (b), (c) handled 500 RED (2 events)
  after_request `>= 500` changed to `>= 400`      -> (c) RED (the 404 reports)
  before_send=scrub_event removed                 -> (f) RED
  request headers kept by _scrub_event            -> (f) RED (X-Cron-Secret leaks)
  the 9+ digit pattern removed                    -> (f) RED (league id), patterns, shape
  scrub_event returns the event on error          -> (f) fail-closed unit + e2e RED
  notify on sentry_sdk.new_scope() (a fork)       -> (g) RED (request, transaction)
  the feedback route's duplicate guard removed    -> (g) RED (a second event)
  ThreadingIntegration(propagate_scope=True)      -> (h) RED
  the 24+ run rule back to "any run" (no digit /  -> (f) patterns RED (both identifiers
    mixed-case check)                                 filtered)
"""
import copy
import logging
import os
import subprocess
import sys
import threading
from pathlib import Path

import pytest

sentry_sdk = pytest.importorskip("sentry_sdk")

from flask import jsonify  # noqa: E402
from sentry_sdk.transport import Transport  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402

import backend.database as db_module  # noqa: E402
import backend.server as server  # noqa: E402
from backend import daily_tick, error_alerts  # noqa: E402
from backend.database import metadata  # noqa: E402
from backend.tests.test_fork_safe_db_and_threads import loop_pass  # noqa: E402,F401 (fixture)

REPO = Path(__file__).resolve().parents[2]
FAKE_DSN = "https://public@example.invalid/1"
BOOM = "admin_experiment_transition_route"        # POST /api/admin/experiments/<key>/transition
UNAVAILABLE = "admin_experiment_decide_route"     # POST /api/admin/experiments/<key>/decide

JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ1c2VyIn0.c2lnbmF0dXJlLXNlY3JldA"
ESPN_S2 = "AEBxyz" + "Q2xvdWQ%2FS2V5%3D" * 8
SWID = "{1A2B3C4D-1111-2222-3333-444455556666}"
LEAGUE = "123456789012345678"
EMAIL = "owner@example.com"
QUERY_TOKEN = "qwerty123456789012345678"
# Kept up here, out of the source context (5 lines either side) the SDK
# attaches to a raising test frame.
BODY_SECRET = "SECRET-BODY-123"
CRON_HEADER_SECRET = "cron-abc"


class _Recorder(Transport):
    """Stores envelopes, with the thread that captured each."""

    def __init__(self, options=None):
        super().__init__(options)
        self.items = []

    def capture_envelope(self, envelope):
        self.items.append((threading.get_ident(), envelope))

    def events(self, thread=None):
        thread = threading.get_ident() if thread is None else thread
        return [env.get_event() for ident, env in self.items
                if ident == thread and env.get_event() is not None]

    def raw(self):
        return b"".join(env.serialize() for _, env in self.items)


def _fresh_scopes():
    sentry_sdk.get_isolation_scope().clear()
    sentry_sdk.get_current_scope().clear()


@pytest.fixture(autouse=True)
def _sentry_off_around():
    assert not sentry_sdk.get_client().is_active()
    yield
    assert not sentry_sdk.get_client().is_active()


@pytest.fixture
def sentry(monkeypatch):
    """Sentry on with a recording transport; off again in teardown."""
    real_init = sentry_sdk.init
    monkeypatch.setattr(sentry_sdk, "init",
                        lambda **kwargs: real_init(transport=_Recorder, **kwargs))
    monkeypatch.setattr(error_alerts, "_initialized", False)
    monkeypatch.setenv("SENTRY_DSN", FAKE_DSN)
    # No background-thread start (win-now-resume) from a first request mid-test.
    monkeypatch.setattr(server, "_bg_threads_pid", os.getpid())
    _fresh_scopes()
    assert error_alerts.init_error_alerts() is True
    try:
        yield sentry_sdk.get_client().transport
    finally:
        sentry_sdk.get_client().close()
        sentry_sdk.get_global_scope().set_client(None)
        _fresh_scopes()


@pytest.fixture
def client():
    return server.app.test_client()


# ── (a) dark without a DSN ─────────────────────────────────────────────────

def test_no_dsn_means_no_client_and_nothing_sent(monkeypatch, client):
    calls = []
    monkeypatch.setattr(sentry_sdk, "init", lambda **kw: calls.append("init"))
    monkeypatch.setattr(sentry_sdk, "capture_message", lambda *a, **kw: calls.append("message"))
    monkeypatch.setattr(sentry_sdk, "capture_event", lambda *a, **kw: calls.append("event"))
    monkeypatch.setattr(error_alerts, "_initialized", False)
    monkeypatch.setitem(server.app.view_functions, UNAVAILABLE,
                        lambda **_: (jsonify({"error": "unavailable"}), 503))
    for value in (None, "", "   "):
        if value is None:
            monkeypatch.delenv("SENTRY_DSN", raising=False)
        else:
            monkeypatch.setenv("SENTRY_DSN", value)
        assert error_alerts.init_error_alerts() is False
    assert not sentry_sdk.get_client().is_active()
    error_alerts.notify("feedback_received", feedback_id=1, kind="bug")
    assert client.post("/api/admin/experiments/x/decide").status_code == 503
    assert calls == []


def test_no_dsn_never_imports_the_sdk():
    env = {k: v for k, v in os.environ.items() if k != "SENTRY_DSN"}
    code = ("import sys; from backend import error_alerts as ea; "
            "assert ea.init_error_alerts() is False; ea.request_started(); "
            "ea.report_5xx(503); ea.notify('x', kind='bug'); "
            "print('sentry_sdk' in sys.modules)")
    out = subprocess.run([sys.executable, "-c", code], cwd=REPO, env=env,
                         capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "False"


def test_init_options(monkeypatch):
    seen = []
    monkeypatch.setattr(sentry_sdk, "init", lambda **kw: seen.append(kw))
    monkeypatch.setattr(error_alerts, "_initialized", False)
    monkeypatch.setenv("SENTRY_DSN", FAKE_DSN)
    monkeypatch.setenv("RENDER_GIT_COMMIT", "0123abcd")
    monkeypatch.delenv("SENTRY_ENVIRONMENT", raising=False)
    assert error_alerts.init_error_alerts() is True
    assert error_alerts.init_error_alerts() is True      # idempotent
    [kw] = seen
    assert (kw["dsn"], kw["environment"], kw["release"]) == (FAKE_DSN, "production", "0123abcd")
    assert kw["send_default_pii"] is False and kw["include_local_variables"] is False
    assert kw["max_request_body_size"] == "never" and kw["max_breadcrumbs"] == 30
    assert "traces_sample_rate" not in kw and "profiles_sample_rate" not in kw
    assert kw["auto_enabling_integrations"] is False and kw["trace_propagation_targets"] == []
    assert kw["before_send"] is error_alerts.scrub_event
    assert kw["before_breadcrumb"] is error_alerts.scrub_breadcrumb
    assert sorted(type(i).__name__ for i in kw["integrations"]) == [
        "FlaskIntegration", "LoggingIntegration", "ThreadingIntegration"]


def test_a_malformed_dsn_leaves_alerts_off(monkeypatch):
    monkeypatch.setattr(error_alerts, "_initialized", False)
    monkeypatch.setenv("SENTRY_DSN", "not-a-dsn")
    assert error_alerts.init_error_alerts() is False
    assert not sentry_sdk.get_client().is_active()


# ── (b) route exceptions ───────────────────────────────────────────────────

def _boom(**_kw):
    raise RuntimeError("synthetic route failure")


def test_a_raising_route_is_one_event_with_its_stack(sentry, monkeypatch, client):
    monkeypatch.setitem(server.app.view_functions, BOOM, _boom)
    res = client.post("/api/admin/experiments/x/transition")
    assert res.status_code == 500 and res.get_json()["error"] == "internal_error"
    [event] = sentry.events()                    # no http_5xx on top of it
    assert event["level"] == "error"
    assert event["logentry"]["message"] == "Unhandled error on %s %s"
    [exc] = event["exception"]["values"]
    assert exc["type"] == "RuntimeError"
    assert "_boom" in [f["function"] for f in exc["stacktrace"]["frames"]]


# ── (c) handled 5xx ────────────────────────────────────────────────────────

def test_a_handled_503_is_one_http_5xx_and_a_404_none(sentry, monkeypatch, client):
    monkeypatch.setitem(server.app.view_functions, UNAVAILABLE,
                        lambda **_: (jsonify({"error": "unavailable"}), 503))
    assert client.post("/api/admin/experiments/x/decide").status_code == 503
    [event] = sentry.events()
    route = "/api/admin/experiments/<key>/decide"
    assert (event["message"], event["level"]) == ("http_5xx", "error")
    assert event["tags"] == {"route": route, "status": "503", "method": "POST"}
    assert event["fingerprint"] == ["http_5xx", route, "503"]
    assert client.get("/api/no-such-route").status_code == 404
    assert len(sentry.events()) == 1


@pytest.fixture
def feedback_db(monkeypatch):
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    metadata.create_all(engine)
    monkeypatch.setattr(db_module, "engine", engine)
    monkeypatch.setattr(server, "record_event", lambda *a, **kw: None)


def test_a_handled_500_after_an_error_log_is_one_event(sentry, feedback_db, monkeypatch, client):
    def broken(**_kw):
        raise RuntimeError("synthetic save failure")
    monkeypatch.setattr(server, "save_feedback", broken)
    res = client.post("/api/feedback", json=_note("fb-alerts-500"))
    assert res.status_code == 500
    [event] = sentry.events()                    # the log.exception; no http_5xx
    assert event["logentry"]["message"] == "save_feedback failed: %s"


# ── (d) the cleanup loop, (e) the daily tick ───────────────────────────────

def test_a_failing_cleanup_step_is_one_event(sentry, monkeypatch, loop_pass):
    def fail():
        raise RuntimeError("synthetic retention failure")
    monkeypatch.setattr(server, "_prune_deck_evidence", fail)
    assert loop_pass() == 2
    [event] = sentry.events()
    assert event["logentry"]["message"] == "deck-evidence retention failed"
    assert event["exception"]["values"][0]["type"] == "RuntimeError"


def test_a_raising_daily_tick_step_is_one_event(sentry):
    def boom(_now):
        raise ValueError("kaput")
    [result] = daily_tick.run([daily_tick.Step("boom", boom)], object(), log=server.log)
    assert result.outcome == "error"
    [event] = sentry.events()                    # the WARNING step line is a breadcrumb
    assert event["logentry"]["message"] == "daily-tick: step %s raised"
    assert event["logentry"]["params"] == ["boom"]
    assert event["exception"]["values"][0]["type"] == "ValueError"


# ── (f) the scrub ──────────────────────────────────────────────────────────

def test_no_secret_reaches_the_envelope(sentry, monkeypatch, client, caplog):
    caplog.set_level(logging.INFO, logger=server.log.name)   # basicConfig's DEBUG, as in prod
    def boom(key):
        server.log.info("looking up league %s for %s", key, EMAIL)   # a breadcrumb
        raise RuntimeError(f"lookup failed for {EMAIL} in league {key}")
    monkeypatch.setitem(server.app.view_functions, BOOM, boom)
    res = client.post(
        f"/api/admin/experiments/{LEAGUE}/transition?token={QUERY_TOKEN}",
        json={"note": BODY_SECRET},
        headers={"Cookie": f"espn_s2={ESPN_S2}; SWID={SWID}",
                 "Authorization": f"Bearer {JWT}", "X-Cron-Secret": CRON_HEADER_SECRET})
    assert res.status_code == 500
    [event] = sentry.events()
    assert event["request"] == {
        "method": "POST", "url": "http://localhost/api/admin/experiments/[Filtered]/transition"}
    assert "user" not in event
    assert "looking up league [Filtered] for [Filtered]" in [
        b["message"] for b in event["breadcrumbs"]["values"]]
    sentry_sdk.flush()
    raw = sentry.raw()
    for secret in (BODY_SECRET, ESPN_S2, SWID[1:-1], JWT, CRON_HEADER_SECRET, QUERY_TOKEN,
                   LEAGUE, EMAIL):
        assert secret.encode() not in raw, secret


@pytest.mark.parametrize("text, expected", [
    (f"Cookie: espn_s2={ESPN_S2}; SWID={SWID}", "Cookie: [Filtered]; SWID=[Filtered]"),
    (f"auth failed: Bearer {JWT}", "auth failed: [Filtered]"),
    (f"jwt {JWT}", "jwt [Filtered]"),
    ("X-Cron-Secret: cron-abc", "X-Cron-Secret: [Filtered]"),
    ("MFL_USER_ID=ahBv1sGSvuWrx0OmPQ%3D%3D", "MFL_USER_ID=[Filtered]"),
    ("APIKEY=abc", "APIKEY=[Filtered]"),
    ('{"password": "two words", "n": 1}', '{"password": [Filtered], "n": 1}'),
    (f"?token={QUERY_TOKEN}&page=2", "?token=[Filtered]&page=2"),
    (f"mail {EMAIL} now", "mail [Filtered] now"),
    ("id 0f8fad5b-d9cb-469f-a165-70867728950e", "id [Filtered]"),
    (f"swid {SWID}", "swid [Filtered]"),
    ("s2 " + ESPN_S2.replace("%2F", "/").replace("%3D", "="), "s2 [Filtered]"),
    # 24+ runs: a token has a digit or both cases; a snake_case identifier survives
    ('relation "prepared_trade_inventories" does not exist',
     'relation "prepared_trade_inventories" does not exist'),
    ("_drop_stale_deck_evidence failed", "_drop_stale_deck_evidence failed"),
    ("tok QwErTyUiOpAsDfGhJkLzXcVbNmQwErTy", "tok [Filtered]"),           # 32, mixed case
    ("key 5f4dcc3b5aa765d61d8327deb882cf99", "key [Filtered]"),           # 32, hex
    ("fernet gAAAAABnK3xYq1_9vTzR2c-ZpLm8wQe4sHjN0bVfXy7UaDiOgPkEtWrS5MhC6lAnJ3uIo",
     "fernet [Filtered]"),
    (f"league {LEAGUE} user 123456789", "league [Filtered] user [Filtered]"),
    ("week 12345678 of 2026", "week 12345678 of 2026"),
    ("Unhandled error on POST /api/feedback", "Unhandled error on POST /api/feedback"),
])
def test_scrub_patterns(text, expected):
    assert error_alerts._scrub_str(text) == expected


def test_scrub_event_shape():
    event = {
        "event_id": "a" * 32, "release": "f" * 40, "level": "error",
        "transaction": "admin_experiment_transition_route",
        "message": f"user {EMAIL} league {LEAGUE}",
        "logentry": {"message": "failed %s %s", "params": [LEAGUE, int(LEAGUE)],
                     "formatted": f"failed {LEAGUE} {int(LEAGUE)}"},
        "exception": {"values": [{
            "type": "RuntimeError", "module": None, "value": f"token=abc SWID={SWID}",
            "mechanism": {"type": "logging", "handled": True},
            "stacktrace": {"frames": [{"function": "_attach_presession_feedback",
                                       "filename": "backend/server.py", "lineno": 3,
                                       "vars": {"note": "MY-PRIVATE-FEEDBACK"}}]}}]},
        "extra": {"user_id": "u1", "nested": {"api_key": "k", "note": "aB" * 15}},
        "contexts": {"trace": {"trace_id": "b" * 32, "span_id": "c" * 16},
                     "custom": {"partner": "p", "text": "id 123456789"}},
        "tags": {"route": "/api/league/<league_id>", "feedback_id": "1234567890123",
                 "kind": "bug", "other": EMAIL, "session": "x"},
        "user": {"id": "u1"},
        "request": {"method": "GET", "url": f"https://h/api/x/{LEAGUE}?token=q#f",
                    "query_string": "token=q", "headers": {"X-Session-Token": "t"},
                    "cookies": {"s": "1"}, "data": "body", "env": {"REMOTE_ADDR": "1.2.3.4"}},
        "breadcrumbs": {"values": [{"message": f"hi {EMAIL}",
                                    "data": {"username": "bob", "n": 5}}]},
    }
    out = error_alerts.scrub_event(copy.deepcopy(event), {})
    for key in ("event_id", "release", "level", "transaction"):
        assert out[key] == event[key]
    assert "user" not in out
    assert out["request"] == {"method": "GET", "url": "https://h/api/x/[Filtered]"}
    assert out["message"] == "user [Filtered] league [Filtered]"
    assert out["logentry"]["params"] == ["[Filtered]", "[Filtered]"]
    [exc] = out["exception"]["values"]
    assert exc["value"] == "token=[Filtered] SWID=[Filtered]"
    assert exc["stacktrace"]["frames"] == [{"function": "_attach_presession_feedback",
                                            "filename": "backend/server.py", "lineno": 3}]
    assert out["extra"] == {"user_id": "[Filtered]",
                            "nested": {"api_key": "[Filtered]", "note": "[Filtered]"}}
    assert out["contexts"] == {"trace": event["contexts"]["trace"],
                               "custom": {"partner": "[Filtered]", "text": "id [Filtered]"}}
    assert out["tags"] == {"route": "/api/league/<league_id>", "feedback_id": "1234567890123",
                           "kind": "bug", "other": "[Filtered]", "session": "[Filtered]"}
    assert out["breadcrumbs"] == {"values": [{"message": "hi [Filtered]",
                                              "data": {"username": "[Filtered]", "n": 5}}]}


def test_scrub_breadcrumb():
    sleeper = {"type": "http", "category": "httplib",
               "data": {"url": "https://api.sleeper.app/v1/user/x", "method": "GET"}}
    assert error_alerts.scrub_breadcrumb(sleeper, {}) is None
    assert error_alerts.scrub_breadcrumb({"type": "http", "category": "x"}, {}) is None
    crumb = {"type": "log", "category": "trade_finder", "message": f"league {LEAGUE}",
             "data": {"email": EMAIL, "n": 1}}
    assert error_alerts.scrub_breadcrumb(crumb, {}) == {
        "type": "log", "category": "trade_finder", "message": "league [Filtered]",
        "data": {"email": "[Filtered]", "n": 1}}


def _raising(*_a, **_kw):
    raise RuntimeError("scrubber bug")


def test_a_scrubber_exception_drops_the_event(monkeypatch):
    monkeypatch.setattr(error_alerts, "_scrub", _raising)
    assert error_alerts.scrub_event({"message": "x"}, {}) is None
    assert error_alerts.scrub_breadcrumb({"message": "x"}, {}) is None


def test_a_scrubber_exception_sends_nothing_and_the_route_still_answers(sentry, monkeypatch,
                                                                        client):
    def boom(key):
        server.log.info("a breadcrumb for %s", key)
        raise RuntimeError(f"lookup failed for {EMAIL}")
    monkeypatch.setattr(error_alerts, "_scrub", _raising)
    monkeypatch.setitem(server.app.view_functions, BOOM, boom)
    assert client.post(f"/api/admin/experiments/{LEAGUE}/transition").status_code == 500
    assert sentry.events() == []
    assert EMAIL.encode() not in sentry.raw()


# ── (g) the feedback_received alert ────────────────────────────────────────

ME = "user_alerts_fb"
TOKEN = "tok-alerts-verified-session"
CLIENT_ID = "fb-alerts-client-id-1"


def _note(client_id=CLIENT_ID):
    return {"client_id": client_id, "screen": "TradesScreen", "severity": "bug",
            "text": "MY-PRIVATE-FEEDBACK", "client_created_at": "2026-10-31T12:00:00Z"}


def test_new_feedback_is_one_tag_only_alert_and_a_duplicate_none(sentry, feedback_db,
                                                                   monkeypatch, client):
    monkeypatch.setitem(server._sessions, TOKEN, {
        "verified": True, "user_id": ME, "username": "me-username",
        "display_name": "Me Display", "last_active": 0.0})
    headers = {"X-Session-Token": TOKEN, "X-Device-Id": "device-alerts-1"}
    res = client.post("/api/feedback", json=_note(), headers=headers)
    assert res.status_code == 201, res.get_json()
    server_id = res.get_json()["server_id"]
    [event] = sentry.events()
    assert (event["message"], event["level"]) == ("feedback_received", "info")
    assert event["tags"] == {"feedback_id": str(server_id), "kind": "bug"}
    assert "request" not in event and "user" not in event and "transaction" not in event
    assert not (event.get("breadcrumbs") or {}).get("values")
    raw = sentry.raw()
    for value in ("MY-PRIVATE-FEEDBACK", "TradesScreen", CLIENT_ID, TOKEN, ME,
                  "me-username", "Me Display", "device-alerts-1"):
        assert value.encode() not in raw, value

    res = client.post("/api/feedback", json=_note(), headers=headers)
    assert res.status_code == 200 and res.get_json()["duplicate"] is True
    assert len(sentry.events()) == 1


# ── (h) threads carry no request ───────────────────────────────────────────

def test_a_thread_started_in_a_request_carries_no_request(sentry, monkeypatch, client):
    ident = []

    def spawn(**_kw):
        worker = threading.Thread(target=lambda: server.log.error("synthetic background failure"))
        worker.start()
        worker.join()
        ident.append(worker.ident)
        return jsonify({"ok": True})
    monkeypatch.setitem(server.app.view_functions, BOOM, spawn)
    assert client.post("/api/admin/experiments/x/transition").status_code == 200
    [event] = [e for e in sentry.events(thread=ident[0])
               if e["logentry"]["message"] == "synthetic background failure"]
    assert "request" not in event
